---
key: FMS-CANONICAL-OWNER-IS-GOVREV-FMS-RAIL
question: >
  Where does canonical Foreign Military Sales congressional-notification truth
  live — inside the existing government_procurement_event.v2 event plane, in a
  new general defense event store, or in a GovRev-owned FMS source
  contract/read model — and which product surface consumes it?
answer: >
  Canonical FMS truth is a GovRev-owned source plane (append-only receipts +
  case observations, D6-A field conventions) with one derived
  government_fms_case.v1-class read model, published through the EXISTING
  GovRev publication lane and entitlement boundary, and consumed by a ninth
  bounded mode (data-mode="fms") on the existing government_revenue.html page
  via two routes in the existing entitled router. FMS v1 emits ZERO
  government_procurement_event.v2 rows and no new general event, identity,
  correction, or publication plane exists. A future stage-transition →
  event-tape bridge is a named rejected-for-now alternative requiring its own
  Sol authorization. Case identity is the source-native transmittal number
  (fms:transmittal:<yy-nn>) with a deterministic URL-path-digest fallback;
  the only v1-provable stage is congressional_notification; the only amount
  semantic is estimated_notification_value.
rationale: >
  government_procurement_event.v2 is award-shaped at the identity level: its
  event_id seed is {award_key, source_rail, state_hash, known_at, event_type,
  changed_fields} (award_events.py:1735-1776), its required fields include
  agency/award_change/listed_company_impacts/primary_ticker, and its runtime
  emits only kind=award_change. An FMS congressional notification has no
  award, different clocks (notification/publication/known_at), a stage ladder
  the contract does not model, and an amount that must never sit one field
  away from award aggregation. Forcing it in is the commissioned kill-test
  T12; extending the live proven award-tape contract for alien semantics
  risks the tape to serve a different source. The D6-A budget rail already
  proved the chosen composition end to end (own source triad + read model +
  bounded page mode + existing entitled API), so option B duplicates nothing
  and invents nothing. 2026-08-25 census: zero existing FMS/DSCA footprint in
  the repo; page-weight headroom 28,890 bytes under the 303,104 fence with an
  8,192-byte frozen shell delta.
alternatives:
  - option: Extend/reuse government_procurement_event.v2 with an FMS kind
    why_not: >
      No semantically honest additive representation exists: the identity
      seed requires award_key, the required-field set is award-shaped, and a
      new kind would modify the live proven award-tape contract for a source
      with incompatible stage/amount/clock semantics. Stuffing FMS into
      kind=award_change is the commissioned adversarial failure T12.
  - option: New general defense event store
    why_not: >
      Presumptively rejected by the D6-B0 commission; violates the standing
      no-duplicate-planes law (a second event/identity/correction/publication
      plane); nothing in the census requires it.
  - option: Widen government_program_dossier.v1 or ship a separate FMS page
    why_not: >
      Dossier widening is explicitly prohibited by the commission; a separate
      page requires estate archaeology proving the existing family cannot
      support the job, and the D6-A budget mode proves the opposite.
  - option: Emit FMS stage transitions onto the changes tape in v1
    why_not: >
      Requires the event contract this decision rejects for FMS; deferred as
      a named future Sol decision with its own kind/identity design.
evidence:
  - "research/defense_intelligence/DEFENSE_D6B_FMS_SOURCE_AND_STAGE_ARCHITECTURE_FREEZE_2026-08-25.md §2 (source census receipts R1-R7), §9 (adjudication), §13 (consumer)"
  - "contracts/government_revenue/government_procurement_event.v2.schema.json — kind enum [opportunity, recompete, award_change]; required fields"
  - "engine/government_revenue/award_events.py:1735-1776 — event identity seed includes award_key; :1921 only award_change emitted"
  - "Repo grep 2026-08-25 (head 99af5edd7626): zero substantive FMS/DSCA references anywhere — clean field"
  - "scripts/build_government_revenue.py:113 RAW_HTML_BUDGET_BYTES=303104; site/government_revenue.html on main = 274214 bytes"
  - "Sol D6-A acceptance ruling authorizing D6-B0 (macro #6385 comment 5404403124)"
affects:
  - "WS:DEFENSE-PROCUREMENT-V3"
  - "engine/government_revenue/"
  - "app/government_revenue.py"
  - "templates/government_revenue.html.j2"
reversibility: costly
decided_by: coo-fable
decided_at: 2026-08-25
confidence: high
notes: >
  Freely reversible by superseding this record until D6-B implementation
  ships; after the FMS rail is live, reversal means a data-plane migration of
  published case identities and read models. The append-only, alias-preserving
  identity/correction laws mean even that migration would not destroy history.
---

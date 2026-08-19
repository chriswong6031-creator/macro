---
key: PROPHET-LAB-B5A-RECUT
question: >
  May the Chairman see exact early-entry candidates live on the Prophet page before
  V4-B3 (orthogonal lifecycle) and V4-B4 (buyability firewall) exist — and if so, how
  is that surfaced without granting the early-entry lane any Prophet authority or
  waiting 10–20 trading days for outcome maturation?
answer: >
  Yes, via a recut of V4-B5. B5A "Prophet Operator Lab" is an operator-only LIVE|LAB
  observational mode on the U.S. Prophet page: a read-only presentation/projection
  layer over canonical Radar output (six frozen Lab boards; read/filter/join/decorate
  only; zero ranking/gating/sizing/plan-origination/signal-origination/
  Prophet-mutation authority; all-false authority block in the API contract). B5A
  ships without B3/B4. B5B "authoritative Early Entry Desk" retains the B3/B4
  dependencies and later adopts B5A's plumbing instead of rebuilding it. Shipping
  B5A completes neither B5B nor B6. Honesty is carried by a Lab-plane observation
  class (retrospective_seed vs live_forward): seeds are visible immediately but
  evidence_eligible=false with measured lead null; only true live-forward
  observations (first_observed_at = the Radar W4 spool envelope pass_ts that first
  carried the event_id) may show a measured Lab→Prophet lead; a missing
  signal_known_ts is never reconstructed; the immutable mastermind.entry_event.v1
  event is never mutated to carry transport facts. Contract:
  research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md; wave-graph ruling 14.
rationale: >
  Direct Chairman commission, 2026-08-18, to the orchestrating Fable session: "This
  program is NOT a request to promote an early-entry detector into Prophet authority.
  It is a read-only operator experiment. Do not wait for 10-20 trading days of outcome
  maturation before making candidates visible." The original B5 conflated an
  observational operator surface with an authoritative desk; only the latter needs
  the B3/B4 truth substrate. Splitting them lets operator inspection start as soon as
  the Radar transport is functional (W4.1) while keeping every authority-bearing
  capability behind its original gates.
alternatives:
  - option: Keep B5 whole and wait for B3/B4
    why_not: >
      Blocks a zero-authority read-only surface on two unstarted waves that exist to
      gate AUTHORITY, not visibility — and directly contradicts the Chairman's
      explicit no-waiting instruction.
  - option: Ship the Lab as a Radar-side page (extend W8/#5737) instead of inside Prophet
    why_not: >
      The commission requires the LIVE|LAB mode inside the U.S. Prophet experience
      with Prophet comparison on every card; W8 is a standalone Radar reference and
      is explicitly NOT this Lab. Radar keeps detector truth; the Prophet page is
      where the operator decision context lives.
  - option: Mark B5/B6 done when the Lab ships
    why_not: >
      The Lab proves visibility, not the desk's authority semantics (B5B) nor
      full-RTH observation-only activation proof (B6). Conflating them is exactly
      the completion inflation the recut exists to prevent.
evidence:
  - "Chairman commission 2026-08-18 (operator chat, verbatim charter held by the commissioning session): LIVE|LAB operator mode, six Lab board definitions, observation-class law, R-LAB-1/P-LAB-API/D-LAB-R5/P-MP1-SHELL/P-LAB-UI execution order"
  - "V4-B5 original definition and deps: research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md §2 Phase 2 (B5 deps B3,B4) at pin fc0557bb0873"
  - "Radar transport defects the Lab depends on, pinned at main a7cfd4bef589: engine/entry_radar/live_eval.py:2090-2104 reads probe_set['nightly_lanes'] which live_pack.py:686-731 probe_set_snapshot() never emits; W4 envelope entry_radar.events/v1 (live_ledger.py:1114-1132) vs W5 schema gate mastermind.entry_event.v1 (scripts/reconcile_entry_radar.py:95,268-271)"
  - "R4 reference is committed but NOT RIG-approved: mockups/refs/institutionalize/us_stocks/DESIGN_NOTES.md:7 'Not self-approved. No approval.yml'; 10 blocking findings in research/reference_integrity/prophet-board-5514-r4/R4_CLOSURE_LEDGER.md — hence D-LAB-R5 is a fresh independent RIG, not a formality"
  - "MP-1 unexecuted: research/migration_packets/MP-1-prophet-board.md Record line (line 153) empty; no implementing PR found"
affects:
  - "research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md"
  - "research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md"
  - "agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md"
  - "agentos/workstreams/WS-LIVE-ENTRY-RADAR.md"
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-18
---

## Grounds

The Chairman's 2026-08-18 commission explicitly separates the observational operator
experiment from detector promotion, orders candidates visible without outcome
maturation, and orders the records-only LAB-0 amendment before any runtime work. The
recut records that separation where the V4 program's dependency law lives (wave-graph
ruling 14) so no later session re-derives B3/B4 as a Lab blocker — or, worse, ships
the Lab and calls the desk done.

## Boundaries that keep this reversible

The Lab is a projection layer with two independent stand-down switches
(`PROPHET_LAB_DISABLED` for the Lab API; Radar's `ENTRY_RADAR_LIVE_DISABLED`/`KILL`
file for the source), defaults to LIVE on every fresh page, retains the nightly DOM
as the runtime restore target, and has no code path that mutates Prophet state.
Deleting the Lab surface restores the pre-LAB-0 product exactly; B5B's charter is
untouched by that deletion.

## What would reopen this

A Chairman/Sol ruling that operator-facing early-entry visibility must wait for the
B3/B4 substrate after all, or evidence that the Lab surface is leaking authority
(anything on it feeding a rank, gate, size, or plan) — the latter is a violation to
fix, not a reason to re-merge the waves.

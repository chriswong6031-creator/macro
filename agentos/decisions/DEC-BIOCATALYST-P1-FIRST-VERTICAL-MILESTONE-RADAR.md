---
key: BIOCATALYST-P1-FIRST-VERTICAL-MILESTONE-RADAR
question: >
  Which post-P0 BioCatalyst vertical ships first: Catalyst Radar —
  Regulatory/PDUFA (Sol's prior), Catalyst Radar — Trial Milestones (registry
  milestone dates with revision lineage), Company/Asset Dossier, or biotech
  Market Pulse? And may the existing milestone monitor — whose docstring says
  it is "deliberately not a catalyst calendar" — be graduated into a Catalyst
  Radar surface?
answer: >
  Catalyst Radar — Trial Milestones, explicitly architected as the reusable
  catalyst-event / evidence / identity spine whose second tenant is
  Regulatory/PDUFA. Named honestly: the source supplies registry
  primary/overall completion dates (often ESTIMATED, sponsor-submitted), which
  are NOT sponsor topline-readout announcements — the vertical, its rows, and
  its API say "trial milestones," and a true readout/announcement calendar
  remains a future cross-plane capability. The graduation of the milestone
  monitor into a Catalyst Radar is a named boundary evolution: the no-signal
  discipline is preserved (no approval/outcome/market-signal claim; rows are
  registry schedule facts with provenance), while the dates are presented as
  watchable catalyst-class events under the spine identity. Sol's PDUFA-first
  prior is revised on readiness evidence (Sol commissioned exactly this
  falsification test). Ratification of BOTH the revision and the boundary
  evolution is returned to Sol before the P1-1 implementation PR is
  commissioned
  (research/BIOCATALYST_P1_RECHARTER_AND_FIRST_VERTICAL_ARCHITECTURE_2026-08-20.md
  §11.1).
rationale: >
  Current-head archaeology (P1-0 census + opus red-team, 2026-08-20):
  prospective PDUFA has no lawful source at current head — pdufa_date is a
  forbidden claim on Drugs@FDA per the RECON-0 freeze, forward PDUFA is
  issuer-disclosure truth owned by the corporate plane (SEC ingest is
  unavailable_to_biocatalyst by registry law), Drugs@FDA is
  production_ingest_allowed false with rights review owed, and the BPC JV
  snapshot is post-soak + SNAPSHOT-ONBOARD gated. The steelman for the prior
  (gates are decisions, soak ends in 6 days) fails because the gates PDUFA
  needs are unopenable by any BioCatalyst act: even same-day rulings yield a
  retrospective approvals spine, not forward PDUFA dates — the missing
  artifact is a cross-plane disclosure-evidence contract that does not exist
  in any form, duration unknown. Trial Milestones runs on the registry's two
  production-allowed sources: clinicaltrials_gov_v2 (the only launch-critical
  one; live generation ctgov_run_20260820T120032611932Z) and
  clinicaltrials_gov_record_history (full contiguous registry version history
  0..N per NCT, 100% cohort coverage — the revision-lineage differentiator).
  Zero-row risk was falsified with real registry data: next_180d yields 1 row
  and next_365d yields 3 rows on the current 4-NCT cohort (NCT06602479 primary
  completion 2026-12-18 Est.; two study completions May 2027); the P0 empty
  state was the next_90d + primary-completion-only default cut. The first
  slice mutates nothing on the frozen soak surface.
alternatives:
  - option: Catalyst Radar — Regulatory/PDUFA first (Sol's prior)
    why_not: >
      Worst end-to-end readiness of the four: blocked on a cross-plane
      issuer-disclosure source contract that does not exist in any form
      (duration unknown), plus Drugs@FDA rights review and the post-soak
      successor-registry transition. Becomes the spine's second tenant instead.
  - option: Keep the milestone monitor's "not a catalyst calendar" boundary
      and ship the radar as a plain calendar upgrade without catalyst framing
    why_not: >
      Rejected as the default, but preserved as Sol's veto option in §11.1:
      the catalyst-event spine (source-native event identity, revision
      lineage, evidence drill-down) is the reusable architecture the program
      needs for every later tenant; shipping it without the spine identity
      would rebuild the same surface twice. The no-signal discipline the
      boundary protects is kept either way.
  - option: Company/Asset Dossier first
    why_not: >
      A join surface whose inputs (catalysts, pipelines, cash/runway, asset
      identity) do not exist yet; inverts the dependency order.
  - option: Biotech Market Pulse first
    why_not: >
      Explicitly ruled out by the commissioning directive as a convenience
      pick; unlocks no event/evidence spine.
evidence:
  - "research/BIOCATALYST_P1_RECHARTER_AND_FIRST_VERTICAL_ARCHITECTURE_2026-08-20.md §3-§5, §9 falsification table"
  - "config/biocatalyst_sources.yml:52,66 clinicaltrials_gov_v2 production-allowed + launch-critical; :128,142 record-history production-allowed (second production-allowed source, revision-lineage supplier); :221-222 drugs_at_fda false + review_required_before_b4; :267-271 SEC owned_by_corporate_plane / unavailable_to_biocatalyst"
  - "research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md — pdufa_date forbidden claim; forward PDUFA owned by corporate plane"
  - "research/biocatalyst_recovery_v2/P0_C2R2_PRODUCTION_ACCEPTANCE_2026-08-20.md — PROVEN_LIVE read path; milestones 200/0 rows explained by next_90d cut"
  - "app/biocatalyst.py:31-33,2543-2545,2647,2249 — milestone kinds, date types, 'deliberately not a catalyst calendar' docstring, whole-interval containment, generation-date anchor"
  - "engine/biocatalyst/trials.py:36-40,56-69 — complete date-field inventory; source_fact authority block"
  - "Public CT.gov v2 registry reads 2026-08-20 for the four cohort NCTs (falsification table in the architecture doc §9)"
  - "DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE"
  - "DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK"
affects:
  - "biocatalyst"
  - "WS:BPC-JV-RECON"
  - "engine/biocatalyst/"
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-20
review_by: 2026-08-27
---

## Grounds

Sol's directive commissioned this adjudication with an explicit falsification
clause: "Do not accept that prior blindly. Falsify it if current-main
archaeology proves another vertical has materially better end-to-end readiness
without shrinking the product." The archaeology did exactly that, and an opus
red-team then attacked the verdict (verdict: UPHOLD WITH REQUIRED CORRECTIONS
— all corrections applied, including the milestone-not-readout rename, the
named boundary evolution, and the real-data zero-row falsification). The
product is not shrunk: the catalyst-event spine (source-native event identity,
scheduled date + precision + registry date type, known_at,
revision/cancellation lineage, issuer resolution with typed unresolved states,
evidence drill-down) is designed regulatory-tenant-ready from day one; PDUFA
rides the same spine the moment its source plane unlocks.

## What would reopen this

Sol vetoing the revision or the boundary evolution at ratification (§11.1 of
the architecture doc); a lawful prospective-PDUFA source materializing before
P1-1 is commissioned (e.g., an early corporate-plane disclosure-evidence
contract); or the post-soak successor transition landing with
SNAPSHOT-ONBOARD commissioned, which would let the PDUFA tenant start in
parallel rather than second.
